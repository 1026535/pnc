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

The automation cannot read the server recommendation, login reward DTO, or Conquest round flags directly. The shared visual recognizer therefore treats popup matching as demand-driven: it establishes ordinary screen identity with blocking popup profiles excluded, and only evaluates popup families when that base identity is `UNKNOWN`. A stable non-loading base identity in the same `(session_id, session_epoch)` observation session disarms the startup-scoped matcher work until the session epoch changes, except for the captured Lucifer and Growth families described below. This is an observation heuristic, not proof that every asynchronous login offer has finished. The still-open popup remains matchable across repeated unknown frames before that transition.

This is a conservative observation gate, not a claim that a popup is eligible to open. Alliance recommendation eligibility remains unproven without the current alliance/server state; its visual profile is only considered in the same unknown-base startup scope. A caller-side event or reward hint can be added when an existing runtime owner exposes one.

## Lucifer and Growth client conditions, reviewed September 22, 2026

Devin's bounded source consultation and the lead's independent source review used
the recovered **5.0.203 / version code 233** Lua and packaged base tables. The
consultation is retained under
`.local-data/devin-game-knowledge/20260922-155225-tool-free-follow-up-consultation-the-prior-read--e8e53f3fdc/`;
the reviewed conclusions and limitations are in
`.local-data/reports/popup-audit-20260922/audit.md`. Confidence is client-source
verified for these paths; live downloaded configuration and server eligibility
were not inspected.

- Scene-load completion arms `BuyGiftData.loginOpenGiftWin`
  (`gameluamain.lua:1502`); the charge-info response updates offer data and calls
  `OpenGiftWin` (`commands/charge/chargecommand.lua:1989-1994`,
  `datas/buygiftdata.lua:2199-2213`). The latter checks castle level, guide state,
  union recommendation, transfer-area/King Return precedence, puzzle state and
  its module-lifetime once flag (`2257-2339`). A deferred response or queue can
  therefore be consistent with an offer appearing after a Home frame.
- `loginOpenGiftOrder` selects the first eligible `LoginOpenGift` entry, subject
  to `IsCanShow` and first-charge rules (`2367-2481`). The packaged list includes
  gift **200101**, localized as **Lucifer**, but not **200001**, localized as
  **Lucifer Special Offer**. A visual profile's name does not establish its
  underlying gift ID. The exact automatic route for the captured Special Offer
  remains unknown; do not infer that 200001 is selected by this priority list.
- **Growth Boost Weekly Pass** is `GiftExclusiveWeekCardBase` **13**. The login
  order can reach `WeekCardsData:loginWeekCardHandler`; its server-derived queue
  contains eligible purchased cards with unclaimed rewards and unpurchased,
  unexpired offers (`datas/weekcardsdata.lua:113-153,344-375`). Closing a card
  opened with `isLoginOpen` invokes the handler again
  (`uis/weekcards/weekcardswin.lua:318-323`). King Return can defer the remaining
  queue. The similar name of the separate GrowingDiscount feature is not
  evidence that it owns this offer.
- `loginOpenGiftWinOpen` is initialized false and set after the login order
  runs. The recovered Lua has no other assignments. This establishes a once
  gate for that Lua module's lifetime, **not** a guaranteed native-process
  lifetime. Reconnect/character-switch Lua resets and the captured offer's
  exact server prerequisites remain unproven. A day-refresh charge-info request
  alone does not reset this flag.

Automation implication: preserve demand-driven family eligibility and skip
checks when impossibility is established for the relevant opening path. Do not
turn the castle/guide aborts for the automatic login path into a rule about
manually opened windows. Neither one Home frame, one successful dismissal nor
the observed 48/74-second delays prove queue exhaustion or a maximum delay.
This review adds no timeout, broad post-Home matching or reconnect experiment.

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

## Growth Boost Weekly Pass offer after castle switching

On September 22, 2026, a PW05 Hopium-recognition run on configured account
`main` tapped the `npc_on_hopium` roster row once at 05:29:22Z; the session then
showed loading, a briefly recognizable Home city frame at 05:29:45Z, loading
again, and a fully rendered full-height **Growth Boost Weekly Pass** offer at
05:30:59Z (final frame, not loading). The frames are native RGBA 900x1600
session captures under
`.local-data/artifacts/2026-09-22/pet_workshop_pw05_hopium_recognition_525807b/`
(frames `0056_core_9_castle_select_after_5` and `0071_c5_final`; a second offer
frame `0070_c5_return_observe_0` carries a different countdown value). The Home
frame and the offer frame are preserved as the chronological fixture pair
`tests/data/screen_recognition/home_city_before_growth_boost_20260922.png` and
`growth_boost_weekly_pass.png`. The installed build was not recorded for this
capture. Confidence: artifact-observed; both static identity anchors match at
confidence 1.0 on both natural offer frames, so they are independent of the
countdown digits.

The offer identity uses two independent static regions — the title artwork and
the central offer artwork — and excludes the back arrow, purchase bar, currency,
countdown, quantities, and daily reward rows. Its dismiss control is a gold
upper-left diamond arrow separately template-matched and typed `popup_back`
(measured `(85, 55)` in the native frame, bounds `(30, 7, 110, 96)`); it is a
measured on-screen tap, never Android Back. The purchase bar is never published
or invoked. Automation implication: this captured Growth family joins the
scoped post-Home exception alongside Lucifer; it is evaluated only when base
identity is unknown, and every other popup family retains its established
post-login expiry. Subsequent PW05 live006 evidence established one measured
tap at `(85, 55)` followed by a fresh Home frame; the shared Growth correction
was accepted at `516f6d3`, as recorded in
`plans/themed/pet-workshop/PNC_PET_WORKSHOP_ROADMAP.md` and the PW05 checkout's
`.local-data/review/pw05/lead-live006-proof.json`. Whether the client can show
this offer again in the same session remains unknown. Recovery still requires
a fresh observation after each measured tap. This note is recognition/session
evidence, not a Workshop simulator rule.

## Savannah close variation, September 22, 2026

Two native RGBA 540x960 `serious_stuff` captures identified the Savannah offer
but measured its existing X at confidence 0.9440277 and 0.9449110, below the
prior 0.95 cutoff. The saved source frame is
`artifacts/2026-09-22/serious_stuff/20260922T152016Z_v08_warmup_0.png`, now retained
as `tests/data/screen_recognition/savannah_hero_offer_warm_20260922.png`; build
unknown. Confidence: artifact-observed and independently replayed through both
production publishers. Both use the same 540x960 reference, so missing resolution
normalization does not explain this failure.

The reviewed calibration changes only this measured X's threshold to 0.94 and
the profile revision. Identity anchors, search region, asset, global matcher
and eligibility policy are unchanged. Both publishers must return the native
bounds `(480, 55, 46, 48)` and action `(503, 79)` with capture provenance. Erased-X
and single-diagonal variants must remain non-actionable. These captured checks
do not establish live dismissal or qualify every future appearance variant;
the current audit records the separate live acceptance status.

The same capture also exposed an independent publication defect: a successful
named identity disabled generic close measurement even when its own X failed.
Both publishers now request the existing modal-owned X detector when an eligible
named `PNC_POPUP` declares an X and modal bounds but has no measured dismissal. A complete
generic modal/X proof retains the known identity and publishes the measured
candidate with its geometric provenance; an empty named control cannot erase it.
The regression restores the former 0.95 cutoff on this native frame and exercises
both publishers and the ordinary recovery executor. Missing-X and single-diagonal
negatives remain non-actionable. Recognized bases and already measured controls
perform no extra generic probe, nor do offers whose declared control is Back or
Get Started. Session family eligibility is unchanged.
Exact update/reconnect and unresolved semantic interruptions retain precedence.
Confidence: saved-frame replay and deterministic regression; live acceptance is
recorded separately by the audit.

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
