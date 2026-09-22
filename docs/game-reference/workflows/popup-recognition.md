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

## Delayed Lucifer offer after a recognizable Home frame

On September 22, 2026, a PW05 startup-recognition run on configured account
`main` captured a Home city frame at 02:01:52Z followed by the full-height
Lucifer Special Offer at 02:02:40Z in the same startup session. Both frames are
native RGBA 900x1600 session captures under
`.local-data/artifacts/2026-09-22/pet_workshop_pw05_recognition_20b39e3_startup/` (frames
`0011_preflight_settle_10` and `0026_c5_final`) and are preserved as the
chronological fixture pair
`tests/data/screen_recognition/home_city_startup_gap_20260922.png` and
`lucifer_special_offer_startup_gap_20260922.png`. The installed build was not
recorded for this capture. Confidence: artifact-observed; replay through the
production publishers matches the reviewed `lucifer_special_offer` profile and
its measured `popup_back` control at `(80, 60)` with confidence 1.0.

Automation implication: this observed Lucifer family must remain eligible after
a base Home identity. It is still evaluated only when base identity is unknown;
known base screens do no popup-template work. Every other popup family retains
its established post-login expiry. The captured sequence supports this scoped
exception, not a general change to popup lifetimes. Whether the client can show
this offer again later in the same session is unknown; no reappearance rule is
claimed.

## King Return welcome entry

On September 21, 2026, a 900×1600 capture from `157_farm` during V44 validation
showed the full-screen text “Greetings! So glad to have you back! Let me help you
catch up.” and one **Get Started** button. The original frame is
`artifacts/2026-09-21/157_farm/20260921T180355Z_core_20260921T180345Z_29a6b69e_0004_core_route_source.png`;
the reviewed screen fixture is `tests/data/screen_recognition/king_return_welcome.png`.
The live observation classified it as `UNKNOWN` with no blocking popup. The user
subsequently dismissed it by tapping Get Started. The active castle and installed
build were not established before the overlay blocked the identity preflight.

The recovered **5.0.203 / version code 233** client identifies this as
`KING_RETURN_ENTRY_WIN`. `commands/kingreturn/kingreturncommand.lua:346-355`
passes the server's `firstLogIn`, `offlineDay`, and end times to
`datas/kingreturndata.lua:137-151`. `CheckEntranceIsOpen` and
`ShowKingReturnEntry` in that data file open the entry window only while a King
Return activity remains active, `FIRST_LOGIN` is true, the transfer-area window
does not take precedence, and the entry has not opened in this session. The
server's eligibility threshold for `firstLogIn` is unknown; the consulted client
does not define an absence-duration threshold.

`uis/kingreturn/kingreturnentrywin.lua:82-87` handles Get Started by clearing
`FIRST_LOGIN` and `isEntryWinShowing`, firing a local entrance-button update
event, and closing the entry window. That handler makes no purchase, claim, or
network request and opens no next screen. The separate login-gift claim sends
`REQ_RECEIVE` and is outside this dismissal. This source finding and the user's
click report support automatic dismissal of this exact entry overlay. The visual
profile requires distinct character and staff artwork; its Get Started control
is measured separately on the current frame. Shared popup recovery makes one tap
and requires a fresh observation. A still-present entry, an unrecognized follow-up
screen, or a different tutorial remains a stop, with no assumed Home transition.
