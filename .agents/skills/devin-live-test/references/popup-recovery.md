# Popup recovery protocol

Worker playbook for unrelated blocking popups that interrupt a live-test assignment. It operationalizes the canonical policy in [test-bluestacks-live](../../test-bluestacks-live/SKILL.md) — canonical bounded recovery first, then a manual tap on an unambiguous dismissal control — and the publication contract in [failure reporting](../../test-bluestacks-live/references/failure-reporting.md). It does not widen authority: every tap stays inside the assigned lease, castle, role, and spending boundary.

## Step 0 — Confirm it is an unrelated popup

Before recovering, check the assignment's expected screens:

- A dialog the assigned workflow produces (a confirmation the feature under test raises, an expected detail panel) is **task-owned**, not a popup — do not dismiss it.
- `alliance_join_landing` (`PNC_ALLIANCE_JOIN`) is the Join Alliance **landing** shown to an alliance-less account: it occludes Home City and deliberately owns no account-mutating action (Join/Create are never automation targets). Its reviewed dismissal is a tap on the background mask — published as `PNC_ALLIANCE_JOIN_DISMISS_MASK` — so canonical recovery can clear a stray instance. Still publish the incident for any interruption; never tap its Join/Create controls.
- A popup that is itself a check's subject is the feature under test, not an interruption.

## Step 1 — Interpret the screenshot

1. Capture a fresh frame through the session (`capture_screenshot_frame`); never identify a popup from a stale capture. When you proceed to a manual tap, bind it to that frame's provenance — `with session.authorized_input(frame.frame_ref): session.tap_point(x, y)` — the same validation the canonical dispatch uses (session/epoch match, latest-frame match, bounded age, no replay). A bare `tap_point` skips that proof; do not use it for dismissal.
2. Prefer the runtime's own observation: when the recognizer matches a known frame it publishes `blocking_popup` / `popup_overlay` with a typed control and measured action point. A typed control is the canonical answer to "which popup" and "where is its dismiss control" — use it.
3. When no typed control is published, interpret the frame against the playbook table below: match the visual cues, then locate the listed dismiss control on the current frame. Search regions are in the `screen_anchors.json` 540×960 reference space; native frames may be larger — the region tells you where to look, the tap lands on the visible control's center in the frame you hold.
4. If the frame matches no known family and shows no unambiguous dismiss control, do not improvise: record the incident (Step 4), stop only the affected check, and continue independent checks.

## Step 2 — Dismiss

1. **Canonical recovery first.** The executor's typed-control path (`decide_popup_recovery` → `_recover_transient_popups`) requires an explicit safe selector per popup — Android Back is forbidden — fresh frame fingerprints and typed-identity one-shot guards, and a bounded distinct-popup budget (default 6); an `UPDATE_CONFIRM` diverts into the bounded update recovery. When it publishes a dismissal action, let it run.
2. **Manual tap when canonical recovery fails or publishes nothing.** Locate the playbook's dismiss control on the fresh frame and tap its center inside `session.authorized_input(frame.frame_ref)`, under the same lease. One tap per popup appearance, then reobserve — never a blind repeat. Under a `read_only` boundary, content popups are not dismissible: canonical recovery refuses the mutation and `tap_point` may raise — publish the incident and mark dependent checks `not_run` instead of attempting dismissal. Typed system dialogs are the exception: when the probe policy enables `allow_system_popup_recovery`, canonical recovery still handles `reconnect_confirm`/`update_confirm` — let it.
3. **Never:** Android Back as a guess, a tap on a purchase bar / price / reward row / claim / join / get-gift control, or any control not listed as a dismissal below. Offer popups carry real purchase controls; only the documented dismiss control is safe.

## Step 3 — Reobserve and resume

1. After each tap, capture a fresh frame. Confirm the popup is gone and establish the new base identity.
2. A second blocking surface may follow (offer queues re-invoke on close). Repeat Steps 1–2 for each recognized popup, bounded — if an unrecognized or persistent blocking surface survives the bounded loop, stop the affected check and record it.
3. Resume the interrupted check once its preconditions hold on a verified frame. The popup interruption is not a feature result: the retried check stands on its own observed postcondition, and the incident is reported independently.

## Step 4 — Report the incident

Every popup interruption publishes an incident even when recovery succeeds — before resuming when safe, never deferred to final handback.

- Folder: `<report_repository_root>/.local-data/reports/popup-audits/records/<incident-id>/` (this installation's shared root is `C:/Users/lebel/pnc`; use the brief's root, not the worker worktree).
- Contents per [failure reporting](../../test-bluestacks-live/references/failure-reporting.md): `README.md`, `record.json`, `sources/` with the blocking frame.
- Popup-specific record minimum: `category: "popup"`, `status: "reported"`, the matched profile/layout id (or `unrecognized`), the dismiss control kind and tap point used, frame dimensions and coordinate space, recovery action and observed result, affected check IDs and their disposition, and the screenshot's SHA-256 under `sources`.
- Link the incident ID and absolute README path from the manifest's `interruptions` entry. Leave `popup-audits/catalog.json` and `INDEX.md` to the collection owner.

## Playbook

Dismiss controls measured on captured frames; regions are 540×960 reference `[x, y, w, h]` from `screen_anchors.json` / `popup-recognition.md`. Reference taps are tagged with their capture's coordinate space — they are evidence of where the control sat, not tap coordinates for your frame; always tap the visible control's center on the frame you hold.

| Popup | Profile / screen | Recognize by | Dismiss control | Region | Reference tap |
|---|---|---|---|---|---|
| Alliance invitation | `alliance_invitation` | portrait art + footer | `cancel` button | `[199, 532, 121, 31]` | ~(260, 547) 540×960 |
| Alliance invitation (legacy) | `alliance_invitation_portrait` | legacy portrait | `cancel` button | `[191, 519, 140, 53]` | ~(261, 545) 540×960 |
| Savannah hero offer | `savannah_hero_offer` | full-height hero offer | `close_x` | `[470, 45, 65, 70]` | (503, 79) 540×960 |
| Lucifer special offer | `lucifer_special_offer` | face + right art, **no X** | `popup_back` gold arrow | `[0, 0, 100, 90]` | (80, 60) 900×1600 |
| Growth weekly pass | `growth_boost_weekly_pass` | title + offer art | `popup_back` gold diamond | `[0, 0, 100, 90]` | (85, 55) 900×1600 |
| Valiant Conquest | `valiant_conquest` | artwork + panel | `close_x` | `[470, 145, 65, 80]` | ~(502, 185) 540×960 |
| VIP daily reset | `vip_daily_reset` (screen `PNC_VIP_DAILY_RESET`) | crest + VIP wordmark | `close_text` | `[160, 525, 230, 90]` | ~(275, 570) 540×960 |
| King Return welcome | `king_return_welcome` | greeting text + one button | `king_return_get_started` | `[195, 485, 160, 80]` | ~(275, 525) 540×960 |
| Game disconnected | `disconnect_reconnect` (OCR layout) | exact disconnect message + CONFIRM | `reconnect_confirm` | OCR-detected | CONFIRM center |
| Update required | `required_game_update` (OCR layout) | "new version detected / confirm to update" + CONFIRM | `update_confirm` | OCR-detected | CONFIRM center |
| Join Alliance landing | `alliance_join_landing` (screen `PNC_ALLIANCE_JOIN`) | Odin portrait + "Join Alliance" banner, occludes Home | `PNC_ALLIANCE_JOIN_DISMISS_MASK` (background mask, `negative_action`) | fixed region `[30, 830, 140, 70]` reference space — mask only, never the banner or buttons | (100, 865) ref |

Notes:

- **Lucifer / Growth have no X** — the only safe dismissal is the gold upper-left arrow; both are live-verified measured taps. Their purchase bars are never published or touched.
- **King Return Get Started** is the dismissal: client source verifies it closes the entry window with no purchase, claim, or request.
- **Update required** — CONFIRM may route to a store/updater flow the worker cannot complete. If the game does not return to a usable screen after confirmation, that is not a transient popup: mark dependent checks `not_run`, publish the incident, and finish remaining safe checks.
- **Reconnect confirm** returns through a loading transition; wait for a stable post-reconnect frame before resuming.
- `alliance_join_landing` — dismisses only through its typed mask candidate (`PNC_ALLIANCE_JOIN_DISMISS_MASK`); its Join/Create controls remain forbidden. See Step 0.

## Stop conditions

Stop the affected check (and report) when: the frame matches no known family and has no unambiguous dismiss control; the popup survives the bounded recovery loop; dismissal would require touching a non-dismissal control; or the post-dismissal state cannot be re-established. Continue every independent check that remains safe — an unrecovered popup on one case is not a batch failure.
