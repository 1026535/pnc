# Popup recognition

## Evidence

This note records client-source evidence from the recovered PNC **5.0.203 / version code 233** APK. The predicate table is an offline source review; no live server response was observed.

| Family | Client predicate | Source | Confidence |
|---|---|---|---|
| Login offers (Savannah family) | `loginOpenGiftWin` and `loginOpenGiftWinOpen` gate the login offer; `loginOpenGiftOrder` scans `LoginOpenGift` entries and `IsCanShow` | `datas/buygiftdata.lua:2298-2339` | Client source verified |
| Alliance recommendation | Requires scene load completion, sufficient castle level, city scene, no buy-gift window, and `!IsHasUnion`; the server recommendation result controls opening | `datas/uniondata.lua:1954-1972` | Client source verified |
| VIP daily reset/login reward | Opens after scene load when `playerVipDto.addExp > 0`; removing the window clears `addExp` | `datas/vipdata.lua:162-173`, `uis/vip/viploginwin.lua:50-53` | Client source verified |
| Valiant Conquest notice | Notice windows are selected from event time remaining and persisted per round by `ConquerWarDataNotice1/2_<round>`; no weekday-only rule is established | `datas/conquerwardata.lua:26-58` | Client source verified |

## Automation implication

The automation cannot read the server recommendation, login reward DTO, or Conquest round flags directly. The shared visual recognizer therefore treats popup matching as demand-driven: it establishes ordinary screen identity with blocking popup profiles excluded, and only evaluates popup families when that base identity is `UNKNOWN`. A stable non-loading base identity in the same `(session_id, session_epoch)` observation session proves the startup/login window has passed and disarms the startup-only login/VIP/Conquest matcher work until the session epoch changes. The still-open popup remains matchable across repeated unknown frames before that transition.

This is a conservative observation gate, not a claim that a popup is eligible to open. Alliance recommendation eligibility remains unproven without the current alliance/server state; its visual profile is only considered in the same unknown-base startup scope. A caller-side event or reward hint can be added when an existing runtime owner exposes one.

## Live Lucifer evidence

On September 15, 2026, the user opened Lucifer Special Offer on configured account
`main`, castle `K157 / Sword NPC`. The 900×1600 capture shows a full-height offer
with no X: the dismiss control is a gold upper-left arrow. Recognition uses two
separate static artwork regions and excludes prices, percentages, reward rows, and
the arrow from identity. The arrow is separately template-matched and typed
`popup_back`; it is a measured on-screen tap, never Android Back. One canonical
executor tap at `(80, 60)` produced a newer Home frame with a distinct fingerprint.
An exact Manage Characters preflight then verified `K157 / Sword NPC / level 29`
and returned Home. No price, reward, resource, account, or castle-switch action ran.
Evidence is recorded in
`.local-data/reports/popup_live_lucifer_main_20260915.json`.
