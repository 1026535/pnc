# Market primary panel

Artifact-observed on September 30, 2026 during the live turn024 target-only
navigation run. The helper acquired the Market body at TEMPLATE score 0.9695,
slot 11, exact point `(492,756)`; the confirmed body tap opened the interior,
yet endpoint frame0036 and final frame0037 classified `UNKNOWN` with no matched
profiles, so the guard correctly refused the Back action and no endpoint return
was attempted. Sources:
`tests/data/screen_recognition/building_routes/market_native_20260930.png`
(frame0036, `20260930T062556Z_core_20260930T062432Z_9511b106_0036_market_endpoint_endpoint_05.png`)
and correlated frame0037 `..._final_screen_06.png`, manifest group
`2026-09-30/devin-live-test_v44-4-integrated-turn024/9511b106`. Native frames
are RGBA 900x1600; installed build was not recorded.

The panel shows the `Market` title, the level badge `14/45`, a marketplace
building illustration, the facility description "A facility that allows you to
exchange resources with your allies.", dynamic `Transport Fee: 27%` and
`Total Resources` rows, the `Resource Transport` panel control, and a measured
top-left Back arrow.

**Repository-proven:** the `building_market` visual profile requires both the
building-illustration anchor and the description anchor; the measured
`PNC_BACK_BUTTON_TOP_LEFT` is the only published control. Identity deliberately
avoids the mutable level badge, dynamic transport values, and overlays; the
illustration reflects the observed level-14 building, so higher-tier art is
unproven. Anchor separation is wide: identity anchors score 1.000 on both
native frames while the best rival frames score at most 0.47 (description) and
0.24 (art). Frame0037 is a same-session correlated validation, not an
independent holdout.

**Authority boundary:** this profile is passive endpoint/Back perception only.
It grants no public Market entry, no transport, glory-level, upgrade, or
spending action, and no navigation return edge. The `PNC_MARKET_*` controls
admitted by the pre-existing OCR text path on content-authorized observations
are unchanged; the visual path publishes Back alone.

**Not yet proven:** a live typed Back return after recognition on the final
candidate, an independent-session appearance holdout, and higher-level Market
art remain unqualified.
