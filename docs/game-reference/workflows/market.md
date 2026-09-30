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

**Live-observed, 2026-09-30, installed build unrecorded:** the turn025
publication helper reacquired the current measured Market body at slot 11
(point `(492,756)`), entered to typed `PNC_MARKET`, and returned to fresh
Home through measured top-left Back at `(81,44)`, including one
current-Market takeover return. Evidence: ignored
`.local-data/devin-live-test/runs/v44-publication-20260928/turn-025/`
`evidence.json`/`handoff.md`; parent review
`.local-data/devin-vision-pipeline/v44-live025-independent-review-20260930.json`.
That observed slot placement is this account's current layout, not a global
mapping.

**Authority boundary:** `reviewed_navigation_edges` now carries the measured
top-left Back -> Home edge for `PNC_MARKET`, so `open_building` and
`open_visible_building` admit Market through the shared measured operation as
a public-route candidate. The developmental helper receipts above qualify the
endpoint's Back behavior; final public-caller validation through production
`open_building` is still pending. This grants no transport, glory-level,
upgrade, or spending action. The `PNC_MARKET_*` controls admitted by the
pre-existing OCR text path on content-authorized observations are unchanged;
the visual path publishes Back alone.

**Not yet proven:** final public-caller validation of the reviewed
entry/return (production `open_building`), an independent-session appearance
holdout, and higher-level Market art remain unqualified.
